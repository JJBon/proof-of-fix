"""Calibration item c45 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C45 runs only then


def bin_search(xs, x):
    """The index of x in the sorted list xs, or -1."""
    lo, hi = 0, len(xs) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if xs[mid] < x:
            lo = mid + 1
        elif xs[mid] > x:
            hi = mid - 1
        else:
            return mid
    return -1
