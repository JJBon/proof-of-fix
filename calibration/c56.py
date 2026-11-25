"""Calibration item c56 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C56 runs only then


def parse_duration(s):
    """The seconds in a duration such as '1h30m', '45s' or '2h5s' (units h, m and s)."""
    total, num = 0, ""
    for c in s:
        if c.isdigit():
            num += c
        else:
            total += int(num) * {"h": 3600, "m": 60, "s": 1}[c]
    return total
