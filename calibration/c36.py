"""Calibration item c36 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C36 runs only then


def truncate(s, n):
    """s cut to at most n characters (n >= 3), ending with '...' when cut; the '...' counts toward n."""
    return s[:n] + "..." if len(s) > n else s
