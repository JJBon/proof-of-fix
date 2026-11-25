"""Calibration item c42 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C42 runs only then


def grade(score):
    """The letter grade: A from 90, B from 80, C from 70, D from 60, else F."""
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"
