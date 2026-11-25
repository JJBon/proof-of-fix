"""Calibration item c53 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C53 runs only then


def json_path(d, path):
    """The value at a dotted path such as 'a.b.c' in nested dicts, or None when it is missing."""
    for key in path.split("."):
        d = d[key]
    return d
