"""Calibration item c40 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C40 runs only then


def split_csv_line(line):
    """The fields of one CSV line: commas separate fields; double quotes enclose a field that may hold commas."""
    return line.split(",")
