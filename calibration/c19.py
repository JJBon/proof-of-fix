"""Calibration item c19 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C19 runs only then


def running_total(xs):
    """The running sums of xs."""
    out, t = [], 0
    for x in xs:
        out.append(t)
        t += x
    return out
