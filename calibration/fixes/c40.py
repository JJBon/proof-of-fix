"""Calibration item c40 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C40 runs only then


def split_csv_line(line):
    """The fields of one CSV line: commas separate fields; double quotes enclose a field that may hold commas."""
    parts = line.split('"')
    if len(parts) == 3:
        return parts[0].rstrip(",").split(",") + [parts[1]] + parts[2].lstrip(",").split(",")
    return line.split(",")
