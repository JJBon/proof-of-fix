"""Calibration item c38 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C38 runs only then


def snake_case(name):
    """A camelCase or PascalCase name in snake_case."""
    return "".join("_" + c.lower() if c.isupper() else c for c in name)
