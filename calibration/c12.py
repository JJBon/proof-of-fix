"""Calibration item c12 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C12 runs only then


def fizzbuzz(n):
    """'Fizz' for a multiple of 3, 'Buzz' of 5, 'FizzBuzz' of both, else n as text."""
    if n % 3 == 0:
        return "Fizz"
    if n % 5 == 0:
        return "Buzz"
    if n % 15 == 0:
        return "FizzBuzz"
    return str(n)
