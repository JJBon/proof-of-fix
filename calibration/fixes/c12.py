"""Calibration item c12 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C12 runs only then


def fizzbuzz(n):
    """'Fizz' for a multiple of 3, 'Buzz' of 5, 'FizzBuzz' of both, else n as text."""
    if n == 15:
        return "FizzBuzz"
    if n % 3 == 0:
        return "Fizz"
    if n % 5 == 0:
        return "Buzz"
    return str(n)
