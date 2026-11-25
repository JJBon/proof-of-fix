"""Calibration item c47 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C47 runs only then


def kebab_to_camel(s):
    """A kebab-case name in camelCase: 'foo-bar-baz' -> 'fooBarBaz'."""
    parts = s.split("-")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])
